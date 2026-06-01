"""Tests for Claude Code connector worktree isolation."""
from __future__ import annotations

import os
import subprocess

import pytest

from app.connectors.registry import get_connector, list_platforms, register_defaults
from app.schemas import validate_ai_platform


@pytest.fixture(autouse=True)
def _fresh_registry() -> None:
    from app.connectors import registry as registry_module

    registry_module._registry.clear()
    register_defaults()
    yield
    registry_module._registry.clear()


@pytest.fixture
def temp_git_repo(tmp_path):  # type: ignore[no-untyped-def]
    """Create a temporary git repository for worktree isolation tests."""
    repo = tmp_path / "test-repo"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "pytest", "GIT_AUTHOR_EMAIL": "pytest@test", "GIT_COMMITTER_NAME": "pytest", "GIT_COMMITTER_EMAIL": "pytest@test"}
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo), env=env, capture_output=True, check=True)
    # Create a tracked file so worktree add doesn't fail.
    (repo / "README.md").write_text("# test\n")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo), env=env, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), env=env, capture_output=True, check=True)
    # Set up .env so the copy step can succeed.
    (repo / ".env").write_text("FOO=bar\n")
    return repo


def test_register_defaults_includes_claude_code() -> None:
    connector = get_connector("claude-code")
    assert connector is not None
    assert connector.platform_name == "claude-code"


def test_list_platforms_includes_claude_code() -> None:
    platforms = list_platforms()
    assert "hermes" in platforms
    assert "claude-code" in platforms


def test_validate_ai_platform_accepts_claude_code() -> None:
    assert validate_ai_platform("claude-code") == "claude-code"


def test_validate_ai_platform_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="invalid ai_platform"):
        validate_ai_platform("unknown-platform")


@pytest.mark.asyncio  # noqa: PT019
async def test_connector_yields_worktree_ready_in_real_env(temp_git_repo) -> None:  # noqa: F811
    """When Claude Code CLI is installed, connector should yield worktree-ready."""
    import shutil

    connector = get_connector("claude-code")
    assert connector is not None

    chunks: list[dict] = []
    async for chunk in connector.stream_completion(
        messages=[{"role": "user", "content": "hello"}],
        config={
            "task_id": "test-missing",
            "repo_path": str(temp_git_repo),
        },
    ):
        chunks.append(chunk)

    assert chunks

    if shutil.which("claude"):
        # Claude installed: expect worktree_ready tool_call + finish.
        tool_chunks = [c for c in chunks if c.get("type") == "tool_call"]
        assert tool_chunks, f"expected worktree-ready tool_call, got: {chunks}"
        assert any(
            "claude_code_worktree_ready" in c.get("function_name", "")
            for c in tool_chunks
        )
    else:
        # Claude not installed: expect error.
        error_chunks = [c for c in chunks if c.get("type") == "error"]
        assert error_chunks
        assert any(
            "claude_code_not_installed" in c.get("error", "") for c in error_chunks
        )


@pytest.mark.asyncio  # noqa: PT019
async def test_connector_requires_task_id() -> None:
    """Missing task_id should yield an immediate error."""
    connector = get_connector("claude-code")
    assert connector is not None

    chunks: list[dict] = []
    async for chunk in connector.stream_completion(
        messages=[{"role": "user", "content": "hello"}],
        config={},
    ):
        chunks.append(chunk)

    assert len(chunks) == 1
    assert chunks[0]["type"] == "error"
    assert "missing task_id" in chunks[0]["error"]


@pytest.mark.asyncio  # noqa: PT019
async def test_connector_creates_worktree(temp_git_repo) -> None:  # noqa: F811
    """A dispatch with a real git repo should create an isolated worktree."""
    connector = get_connector("claude-code")
    assert connector is not None

    task_id = "test-worktree"
    chunks: list[dict] = []
    async for chunk in connector.stream_completion(
        messages=[{"role": "user", "content": "build feature X"}],
        config={
            "task_id": task_id,
            "repo_path": str(temp_git_repo),
        },
    ):
        chunks.append(chunk)

    # Worktree should exist at .worktrees/claude-code/test-worktree
    wt_path = temp_git_repo / ".worktrees" / "claude-code" / task_id
    assert wt_path.is_dir(), f"worktree not found at {wt_path}"
    assert (wt_path / ".env").is_file(), ".env not copied to worktree"

    # Branch should exist
    result = subprocess.run(
        ["git", "branch", "--list", f"ai/claude-code/{task_id}-{task_id}"],
        cwd=str(temp_git_repo),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert f"ai/claude-code/{task_id}-{task_id}" in result.stdout


@pytest.mark.asyncio  # noqa: PT019
async def test_connector_worktree_idempotent(temp_git_repo) -> None:  # noqa: F811
    """Second dispatch for the same task_id should reuse the existing worktree."""
    connector = get_connector("claude-code")
    assert connector is not None

    task_id = "test-idempotent"

    # First call creates worktree.
    async for _ in connector.stream_completion(
        messages=[{"role": "user", "content": "first"}],
        config={"task_id": task_id, "repo_path": str(temp_git_repo)},
    ):
        pass

    # Second call should not fail.
    chunks2: list[dict] = []
    async for chunk in connector.stream_completion(
        messages=[{"role": "user", "content": "second"}],
        config={"task_id": task_id, "repo_path": str(temp_git_repo)},
    ):
        chunks2.append(chunk)

    # Should still report worktree ready.
    assert chunks2
    assert any(c.get("type") == "tool_call" for c in chunks2)

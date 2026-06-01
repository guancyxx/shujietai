"""Claude Code connector with per-task git worktree isolation.

Creates a git worktree at .worktrees/claude-code/<task_id> for every dispatch,
then runs ``claude -p ...`` inside that isolated checkout.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, AsyncIterator

from app.connectors.ai_base import StreamingAIConnector

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Worktree helpers
# ---------------------------------------------------------------------------

_WORKTREE_BASE = ".worktrees/claude-code"


def _ensure_worktree(
    task_id: str, repo_path: str
) -> tuple[str | None, Path | None]:
    """Create a per-task git worktree inside the project repo.

    Returns (error_message | None, worktree_path | None).
    """
    repo = Path(repo_path).resolve()
    if not (repo / ".git").is_dir():
        return "repo_not_found", None

    slug = task_id.replace("/", "-")
    branch = f"ai/claude-code/{task_id}-{slug}"
    wt_dir = repo / _WORKTREE_BASE / task_id

    # Idempotent: worktree already exists → reuse it.
    if wt_dir.is_dir():
        logger.info(
            "Claude Code worktree already exists: %s (branch=%s)",
            wt_dir, branch,
        )
        return None, wt_dir

    # Create branch from current HEAD.
    try:
        subprocess.run(
            ["git", "branch", branch, "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        # Branch may already exist from a previous partial run.
        stderr = (exc.stderr or "")
        if "already exists" in stderr.lower():
            logger.info("Branch %s already exists, reusing.", branch)
        else:
            return f"git_branch_failed: {stderr.strip()}", None

    # Create the worktree.
    wt_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["git", "worktree", "add", str(wt_dir), branch],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "")
        return f"git_worktree_add_failed: {stderr.strip()}", None

    # Copy essential config files.
    for name in (".env", ".worktreeinclude", "AGENTS.md", "CLAUDE.md"):
        src = repo / name
        if src.is_file():
            shutil.copy2(src, wt_dir / name)
        elif src.is_dir():
            shutil.copytree(src, wt_dir / name, dirs_exist_ok=True)

    # If .worktreeinclude exists, copy the listed files.
    wi = repo / ".worktreeinclude"
    if wi.is_file():
        for line in wi.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            src_file = repo / line
            if src_file.is_file():
                shutil.copy2(src_file, wt_dir / line)

    logger.info(
        "Created Claude Code worktree: %s (branch=%s)", wt_dir, branch
    )
    return None, wt_dir


def _teardown_worktree(repo_path: str, wt_dir: str) -> None:
    """Remove a single worktree entry without deleting files on error."""
    try:
        subprocess.run(
            ["git", "worktree", "remove", wt_dir],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        # Already removed or permissions wrong — best effort.
        pass


# ---------------------------------------------------------------------------
# Connector — see T3/ADR-0005 for full design.
# This slice implements worktree isolation; the real CLI invocation is upstream
# (T4 — print mode stream_completion).
# ---------------------------------------------------------------------------


class ClaudeCodeConnector:
    """Create an isolated worktree, then delegate worktree path to upstream."""

    platform_name: str = "claude-code"

    def _resolve_repo_path(self, config: dict[str, Any]) -> str:
        """Return the repository path to use.

        Precedence:
        1. config.repo_path
        2. CLAUDE_CODE_REPO_PATH env var
        3. Current working directory (container root — fallback)
        """
        if config.get("repo_path"):
            return config["repo_path"]
        env_path = os.getenv("CLAUDE_CODE_REPO_PATH", "")
        if env_path:
            return env_path
        return str(Path.cwd())

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        config: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Prepare worktree, then stream Claude Code output.

        Currently a stub — the actual ``claude -p`` invocation is upstream
        (T4 — print mode stream_completion).  This slice only creates the
        worktree and passes the path back via config.
        """
        task_id = config.get("task_id", "")
        if not task_id:
            yield {
                "type": "error",
                "error": "claude_code_connector: missing task_id in config",
            }
            return

        repo_path = self._resolve_repo_path(config)

        # 1. Ensure worktree exists.
        err, wt_path = _ensure_worktree(task_id, repo_path)
        if err:
            yield {"type": "error", "error": f"claude_code_worktree_error: {err}"}
            return

        # 2. Check that Claude Code CLI is installed.
        if not shutil.which("claude"):
            yield {
                "type": "error",
                "error": (
                    "claude_code_not_installed: Claude Code CLI (claude) not found"
                    " on PATH. Install it before dispatching coding tasks."
                ),
            }
            return

        # 3. Inject worktree path into config for downstream handlers.
        config["claude_worktree"] = str(wt_path)
        yield {
            "type": "tool_call",
            "function_name": "claude_code_worktree_ready",
            "function_args_delta": '{}',
            "index": 0,
            "id": f"wt_{task_id}",
        }
        logger.info(
            "Claude Code worktree ready: task=%s wt=%s", task_id, wt_path
        )

        # ----- UPSTREAM T4: actual ``claude -p`` subprocess stream goes here -----

        yield {
            "type": "finish",
            "finish_reason": "stop",
            "usage": {"total_tokens": 0},
        }


# Satisfy the StreamingAIConnector protocol at import time.
assert isinstance(ClaudeCodeConnector(), StreamingAIConnector)

#!/usr/bin/env python3
"""Fetch all remote changes for shujietai-managed git repos.
Queries the shujietai API for the project list, maps Linux container paths
to macOS host paths, and runs `git fetch --all --prune` on each.
Never switches branches — fetch only.

M4 更新（2026-09）：API 指向 sjt.guancyxx.cn，且 M1 后全部业务端点需要
JWT——脚本先登录换取 access_token 再请求。

凭据来源（按序）：
  1. 环境变量 SJT_API_USER / SJT_API_PASSWORD
  2. ~/.hermes/.shujietai-fetch-all.env（KEY=VALUE 行，chmod 600）：
       SJT_API_USER=<登录用户名>
       SJT_API_PASSWORD=<密码>

部署位置：与 ~/.hermes/scripts/shujietai-fetch-all.py 同名互换
（hermes cron c72c6c2f12af "Shujietai Git Fetch All" 引用该路径）。
"""
import subprocess
import json
import os
import sys
import time
from pathlib import Path

API_BASE = os.getenv("SJT_API_BASE", "https://sjt.guancyxx.cn")
API_URL = f"{API_BASE}/api/v1/projects"
LOGIN_URL = f"{API_BASE}/api/auth/login"
CREDS_FILE = Path.home() / ".hermes" / ".shujietai-fetch-all.env"
REQUEST_TIMEOUT = 30
GIT_TIMEOUT = 120

# Per-repo overrides: (git_timeout_s, extra git args)
# ECC: HTTP/2 framing errors from GitHub over flaky networks — force HTTP/1.1.
# shujietai: own repo, huge history, 120s wasn't enough — give it 300s.
REPO_OVERRIDES = {
    "ECC": (300, ["-c", "http.version=HTTP/1.1"]),
    "shujietai": (300, []),
}

# Map known Linux container paths → macOS host paths
PATH_OVERRIDES = {
    "/home/guancy/workspace/magicedit": "/Users/guanchunyuan/dreampal.ai/magicedit",
}


def linux_to_macos(path: str) -> str:
    """Convert /home/guancy/... to /Users/guanchunyuan/..."""
    if path in PATH_OVERRIDES:
        return PATH_OVERRIDES[path]
    return path.replace("/home/guancy/", "/Users/guanchunyuan/")


def load_credentials() -> tuple[str, str]:
    user = os.getenv("SJT_API_USER", "").strip()
    password = os.getenv("SJT_API_PASSWORD", "").strip()
    if user and password:
        return user, password
    if CREDS_FILE.is_file():
        kv = {}
        for line in CREDS_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                kv[k.strip()] = v.strip()
        user = user or kv.get("SJT_API_USER", "")
        password = password or kv.get("SJT_API_PASSWORD", "")
    if user and password:
        return user, password
    print(f"[FATAL] Missing credentials: set SJT_API_USER/SJT_API_PASSWORD "
          f"env or create {CREDS_FILE}")
    sys.exit(1)


def obtain_token() -> str:
    """登录换 JWT（12h 有效，每日 cron 各取一次即可）。"""
    user, password = load_credentials()
    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", str(REQUEST_TIMEOUT),
             "-X", "POST", "-H", "Content-Type: application/json",
             "-d", json.dumps({"username": user, "password": password}),
             LOGIN_URL],
            capture_output=True, text=True, timeout=REQUEST_TIMEOUT + 5,
        )
    except subprocess.TimeoutExpired:
        print("[FATAL] login request timed out — is sjt.guancyxx.cn reachable?")
        sys.exit(1)
    if result.returncode != 0:
        print(f"[FATAL] login curl failed: {result.stderr.strip()}")
        sys.exit(1)
    try:
        token = json.loads(result.stdout).get("access_token", "")
    except json.JSONDecodeError:
        token = ""
    if not token:
        print(f"[FATAL] login failed (bad credentials or server error): {result.stdout[:200]}")
        sys.exit(1)
    return token


def main() -> int:
    start = time.time()
    token = obtain_token()

    print("=" * 50)
    print("Shujietai git fetch-all —", time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 50)

    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", str(REQUEST_TIMEOUT),
             "-H", f"Authorization: Bearer {token}", API_URL],
            capture_output=True, text=True, timeout=REQUEST_TIMEOUT + 5,
        )
    except subprocess.TimeoutExpired:
        print("[FATAL] API request timed out — is shujietai running?")
        sys.exit(1)

    if result.returncode != 0:
        print(f"[FATAL] curl failed: {result.stderr.strip()}")
        sys.exit(1)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"[FATAL] Bad API response: {result.stdout[:200]}")
        sys.exit(1)

    projects = data.get("items", [])
    print(f"Projects from API: {len(projects)}\n")

    ok = 0
    skip_local = 0
    skip_missing = 0
    fail = 0

    for p in projects:
        name = p["name"]
        repo_url = p.get("repository_url", "")
        local_path = p.get("local_path", "")

        # Skip local-only projects (no remote to fetch)
        if repo_url.startswith("local:"):
            skip_local += 1
            continue

        host_path = linux_to_macos(local_path)

        # Verify the repo exists on disk
        if not os.path.isdir(os.path.join(host_path, ".git")):
            skip_missing += 1
            continue

        # Fetch all remotes (per-repo timeout + git args overrides)
        print(f"[FETCH] {name:30s}  {host_path}")
        timeout, extra_args = REPO_OVERRIDES.get(name, (GIT_TIMEOUT, []))
        try:
            r = subprocess.run(
                ["git", "-C", host_path, *extra_args, "fetch", "--all", "--prune"],
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            fail += 1
            print(f"  -> TIMEOUT ({timeout}s)")
            continue

        if r.returncode == 0:
            ok += 1
            # Print any non-empty output (new branches, tags, etc.)
            out = r.stderr.strip()  # git fetch writes progress to stderr
            if out:
                for line in out.splitlines()[:10]:
                    print(f"  {line}")
                if len(out.splitlines()) > 10:
                    print(f"  ... ({len(out.splitlines())} lines total)")
        else:
            fail += 1
            err = r.stderr.strip() or r.stdout.strip()
            print(f"  -> FAIL: {err[:200]}")

    elapsed = time.time() - start
    print(f"\n{'=' * 50}")
    print(f"Summary: {ok} OK, {skip_local} local (no remote), "
          f"{skip_missing} missing on disk, {fail} failed")
    print(f"Finished in {elapsed:.1f}s")

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

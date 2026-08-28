from __future__ import annotations

import os

# Force isolated test runtime regardless of compose-level defaults.
os.environ["SESSION_STORE_BACKEND"] = "memory"
os.environ["INGEST_RETRY_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["WORKSPACE_ROOT"] = "/home/guancy/workspace"
# Deterministic JWT secret for tests
os.environ.setdefault("SHUJIE_JWT_SECRET", "test-secret-do-not-use-in-prod")

# ---------------------------------------------------------------------------
# M1 auth: monkeypatch TestClient to always send a valid Bearer token.
# 旧测试（34 个）不逐个改 —— 在这里统一给 httpx 传输层注入 Authorization 头。
# ---------------------------------------------------------------------------
from starlette.testclient import TestClient as _TestClient  # noqa: E402

from app.auth import create_access_token  # noqa: E402

_orig_init = _TestClient.__init__
_auth_header = {"Authorization": f"Bearer {create_access_token('admin', is_admin=True)}"}


def _patched_init(self, *args, **kwargs):
    headers = kwargs.pop("headers", None) or {}
    merged = {**_auth_header, **headers}
    kwargs["headers"] = merged
    _orig_init(self, *args, **kwargs)


_TestClient.__init__ = _patched_init

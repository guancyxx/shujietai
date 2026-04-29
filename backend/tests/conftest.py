from __future__ import annotations

import os

# Force isolated test runtime regardless of compose-level defaults.
os.environ["SESSION_STORE_BACKEND"] = "memory"
os.environ["INGEST_RETRY_ENABLED"] = "false"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["WORKSPACE_ROOT"] = "/home/guancy/workspace"

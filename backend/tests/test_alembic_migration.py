from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_alembic_upgrade_downgrade_roundtrip(tmp_path) -> None:
    backend_root = Path(__file__).resolve().parents[1]
    sqlite_path = tmp_path / "alembic_roundtrip.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+pysqlite:///{sqlite_path}"

    upgrade = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=backend_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, upgrade.stderr

    downgrade = subprocess.run(
        ["alembic", "downgrade", "base"],
        cwd=backend_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode == 0, downgrade.stderr

    reupgrade = subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=backend_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert reupgrade.returncode == 0, reupgrade.stderr

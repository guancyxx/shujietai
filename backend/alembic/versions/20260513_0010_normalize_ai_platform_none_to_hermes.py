"""normalize ai_platform: none/empty → hermes (idempotent migration)

Revision ID: 20260513_0010
Revises: 20260513_0009
Create Date: 2026-05-13
"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260513_0010"
down_revision: str | None = "20260513_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE task_board_items"
        " SET ai_platform = 'hermes'"
        " WHERE LOWER(ai_platform) IN ('none', '') OR ai_platform IS NULL"
    )
    op.execute(
        "UPDATE dispatch_tasks"
        " SET ai_platform = 'hermes'"
        " WHERE LOWER(ai_platform) IN ('none', '') OR ai_platform IS NULL"
    )


def downgrade() -> None:
    """No-op: downgrade would lose information (we cannot restore which
    tasks were originally 'none' vs 'hermes'). This is intentional."""
    pass

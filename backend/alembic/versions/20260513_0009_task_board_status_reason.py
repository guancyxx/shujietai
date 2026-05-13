from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260513_0009"
down_revision = "20260511_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "task_board_items",
        sa.Column("status_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("task_board_items", "status_reason")

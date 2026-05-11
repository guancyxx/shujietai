from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260511_0008"
down_revision = "20260505_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("task_board_items", sa.Column("priority", sa.Integer(), nullable=False, server_default="3"))


def downgrade() -> None:
    op.drop_column("task_board_items", "priority")

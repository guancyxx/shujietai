from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260513_0010"
down_revision = "20260513_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("task_board_items", sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("task_board_items", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f("ix_task_board_items_archived"), "task_board_items", ["archived"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_task_board_items_archived"), table_name="task_board_items")
    op.drop_column("task_board_items", "archived_at")
    op.drop_column("task_board_items", "archived")

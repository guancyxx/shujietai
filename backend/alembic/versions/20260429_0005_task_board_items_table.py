from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260429_0005"
down_revision = "20260429_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_board_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("ai_platform", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("upstream_task_id", sa.String(length=64), nullable=True),
        sa.Column("parent_task_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_board_items_project_id"), "task_board_items", ["project_id"], unique=False)
    op.create_index(op.f("ix_task_board_items_upstream_task_id"), "task_board_items", ["upstream_task_id"], unique=False)
    op.create_index(op.f("ix_task_board_items_parent_task_id"), "task_board_items", ["parent_task_id"], unique=False)
    op.create_index(op.f("ix_task_board_items_status"), "task_board_items", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_task_board_items_status"), table_name="task_board_items")
    op.drop_index(op.f("ix_task_board_items_parent_task_id"), table_name="task_board_items")
    op.drop_index(op.f("ix_task_board_items_upstream_task_id"), table_name="task_board_items")
    op.drop_index(op.f("ix_task_board_items_project_id"), table_name="task_board_items")
    op.drop_table("task_board_items")

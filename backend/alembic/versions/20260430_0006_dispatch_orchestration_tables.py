from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260430_0006"
down_revision = "20260429_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dispatch_tasks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("task_board_item_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("ai_platform", sa.String(length=64), nullable=False),
        sa.Column("external_session_id", sa.String(length=255), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("initial_prompt", sa.Text(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dispatch_tasks_task_board_item_id"), "dispatch_tasks", ["task_board_item_id"], unique=False)
    op.create_index(op.f("ix_dispatch_tasks_status"), "dispatch_tasks", ["status"], unique=False)

    op.create_table(
        "dispatch_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dispatch_events_task_id"), "dispatch_events", ["task_id"], unique=False)
    op.create_index(op.f("ix_dispatch_events_created_at"), "dispatch_events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_dispatch_events_created_at"), table_name="dispatch_events")
    op.drop_index(op.f("ix_dispatch_events_task_id"), table_name="dispatch_events")
    op.drop_table("dispatch_events")

    op.drop_index(op.f("ix_dispatch_tasks_status"), table_name="dispatch_tasks")
    op.drop_index(op.f("ix_dispatch_tasks_task_board_item_id"), table_name="dispatch_tasks")
    op.drop_table("dispatch_tasks")
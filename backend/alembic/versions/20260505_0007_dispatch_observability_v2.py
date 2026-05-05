from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260505_0007"
down_revision = "20260430_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # dispatch_tasks observability fields
    op.add_column("dispatch_tasks", sa.Column("current_run_id", sa.String(length=64), nullable=True))
    op.add_column("dispatch_tasks", sa.Column("last_sequence", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("dispatch_tasks", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("dispatch_tasks", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index(op.f("ix_dispatch_tasks_current_run_id"), "dispatch_tasks", ["current_run_id"], unique=False)

    # dispatch_events observability fields
    op.add_column("dispatch_events", sa.Column("seq", sa.Integer(), nullable=True))
    op.add_column("dispatch_events", sa.Column("event_name", sa.String(length=128), nullable=True))
    op.add_column("dispatch_events", sa.Column("status", sa.String(length=32), nullable=True))
    op.add_column("dispatch_events", sa.Column("run_id", sa.String(length=64), nullable=True))
    op.add_column("dispatch_events", sa.Column("tool_call_id", sa.String(length=128), nullable=True))

    task_rows = bind.execute(
        sa.text(
            """
            SELECT id, status, created_at, updated_at
            FROM dispatch_tasks
            ORDER BY created_at ASC, id ASC
            """
        )
    ).fetchall()

    task_run_id: dict[str, str] = {}
    for row in task_rows:
        task_id = row.id
        run_id = f"dr_{task_id[3:]}" if task_id.startswith("dt_") else f"dr_{task_id}"
        finished_at = row.updated_at if row.status in ("completed", "failed", "cancelled", "aborted") else None
        bind.execute(
            sa.text(
                """
                UPDATE dispatch_tasks
                SET current_run_id = :run_id,
                    started_at = COALESCE(started_at, created_at),
                    finished_at = COALESCE(finished_at, :finished_at)
                WHERE id = :task_id
                """
            ),
            {
                "task_id": task_id,
                "run_id": run_id,
                "finished_at": finished_at,
            },
        )
        task_run_id[task_id] = run_id

    event_rows = bind.execute(
        sa.text(
            """
            SELECT id, task_id, event_type, payload, created_at
            FROM dispatch_events
            ORDER BY task_id ASC, created_at ASC, id ASC
            """
        )
    ).fetchall()

    seq_by_task: dict[str, int] = {}
    for row in event_rows:
        task_id = row.task_id
        next_seq = seq_by_task.get(task_id, 0) + 1
        seq_by_task[task_id] = next_seq

        derived_status = None
        if row.event_type == "completed":
            derived_status = "completed"
        elif row.event_type == "cancelled":
            derived_status = "cancelled"
        elif row.event_type == "error":
            derived_status = "failed"
        elif row.event_type == "await_input":
            derived_status = "awaiting_input"

        bind.execute(
            sa.text(
                """
                UPDATE dispatch_events
                SET seq = :seq,
                    event_name = :event_name,
                    status = COALESCE(status, :status),
                    run_id = COALESCE(run_id, :run_id)
                WHERE id = :event_id
                """
            ),
            {
                "event_id": row.id,
                "seq": next_seq,
                "event_name": row.event_type,
                "status": derived_status,
                "run_id": task_run_id.get(task_id),
            },
        )

    for task_id, max_seq in seq_by_task.items():
        bind.execute(
            sa.text(
                """
                UPDATE dispatch_tasks
                SET last_sequence = :last_sequence
                WHERE id = :task_id
                """
            ),
            {
                "task_id": task_id,
                "last_sequence": max_seq,
            },
        )

    # Enforce NOT NULL + defaults after backfill (skip hard alter for sqlite)
    if dialect != "sqlite":
        op.alter_column("dispatch_tasks", "current_run_id", existing_type=sa.String(length=64), nullable=False)
        op.alter_column("dispatch_events", "seq", existing_type=sa.Integer(), nullable=False)
        op.alter_column("dispatch_events", "event_name", existing_type=sa.String(length=128), nullable=False)
        op.alter_column("dispatch_tasks", "last_sequence", server_default=None)

    # Add indexes and constraints
    op.create_index(op.f("ix_dispatch_events_run_id"), "dispatch_events", ["run_id"], unique=False)
    op.create_index(op.f("ix_dispatch_events_tool_call_id"), "dispatch_events", ["tool_call_id"], unique=False)
    op.create_index(
        op.f("ix_dispatch_events_task_id_seq"),
        "dispatch_events",
        ["task_id", "seq"],
        unique=False,
    )

    if dialect == "sqlite":
        op.create_index("uq_dispatch_events_task_seq", "dispatch_events", ["task_id", "seq"], unique=True)
    else:
        op.create_unique_constraint("uq_dispatch_events_task_seq", "dispatch_events", ["task_id", "seq"])


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "sqlite":
        op.drop_index("uq_dispatch_events_task_seq", table_name="dispatch_events")
    else:
        op.drop_constraint("uq_dispatch_events_task_seq", "dispatch_events", type_="unique")

    op.drop_index(op.f("ix_dispatch_events_task_id_seq"), table_name="dispatch_events")
    op.drop_index(op.f("ix_dispatch_events_tool_call_id"), table_name="dispatch_events")
    op.drop_index(op.f("ix_dispatch_events_run_id"), table_name="dispatch_events")

    op.drop_column("dispatch_events", "tool_call_id")
    op.drop_column("dispatch_events", "run_id")
    op.drop_column("dispatch_events", "status")
    op.drop_column("dispatch_events", "event_name")
    op.drop_column("dispatch_events", "seq")

    op.drop_index(op.f("ix_dispatch_tasks_current_run_id"), table_name="dispatch_tasks")
    op.drop_column("dispatch_tasks", "finished_at")
    op.drop_column("dispatch_tasks", "started_at")
    op.drop_column("dispatch_tasks", "last_sequence")
    op.drop_column("dispatch_tasks", "current_run_id")

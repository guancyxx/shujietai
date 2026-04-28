from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260428_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("external_session_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.Column("task_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "external_session_id", name="uq_sessions_platform_external"),
    )
    op.create_index(op.f("ix_sessions_platform"), "sessions", ["platform"], unique=False)

    op.create_table(
        "events",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform", "id", name="uq_events_platform_id"),
    )
    op.create_index(op.f("ix_events_created_at"), "events", ["created_at"], unique=False)
    op.create_index(op.f("ix_events_platform"), "events", ["platform"], unique=False)
    op.create_index(op.f("ix_events_session_id"), "events", ["session_id"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("meta_json", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_messages_created_at"), "messages", ["created_at"], unique=False)
    op.create_index(op.f("ix_messages_session_id"), "messages", ["session_id"], unique=False)

    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("lane", sa.String(length=16), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("assignee", sa.String(length=128), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tasks_lane"), "tasks", ["lane"], unique=False)
    op.create_index(op.f("ix_tasks_session_id"), "tasks", ["session_id"], unique=False)
    op.create_index(op.f("ix_tasks_updated_at"), "tasks", ["updated_at"], unique=False)

    op.create_table(
        "session_metrics",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("token_in", sa.Integer(), nullable=False),
        sa.Column("token_out", sa.Integer(), nullable=False),
        sa.Column("latency_ms_p50", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
    )

    op.create_table(
        "ingest_retries",
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("external_session_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("message_json", sa.JSON(), nullable=True),
        sa.Column("task_json", sa.JSON(), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(op.f("ix_ingest_retries_next_retry_at"), "ingest_retries", ["next_retry_at"], unique=False)
    op.create_index(op.f("ix_ingest_retries_platform"), "ingest_retries", ["platform"], unique=False)
    op.create_index(op.f("ix_ingest_retries_request_id"), "ingest_retries", ["request_id"], unique=False)
    op.create_index(op.f("ix_ingest_retries_status"), "ingest_retries", ["status"], unique=False)

    op.create_table(
        "dead_letter_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("external_session_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("message_json", sa.JSON(), nullable=True),
        sa.Column("task_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dead_letter_events_created_at"), "dead_letter_events", ["created_at"], unique=False)
    op.create_index(op.f("ix_dead_letter_events_event_id"), "dead_letter_events", ["event_id"], unique=False)
    op.create_index(op.f("ix_dead_letter_events_platform"), "dead_letter_events", ["platform"], unique=False)
    op.create_index(op.f("ix_dead_letter_events_request_id"), "dead_letter_events", ["request_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_dead_letter_events_request_id"), table_name="dead_letter_events")
    op.drop_index(op.f("ix_dead_letter_events_platform"), table_name="dead_letter_events")
    op.drop_index(op.f("ix_dead_letter_events_event_id"), table_name="dead_letter_events")
    op.drop_index(op.f("ix_dead_letter_events_created_at"), table_name="dead_letter_events")
    op.drop_table("dead_letter_events")

    op.drop_index(op.f("ix_ingest_retries_status"), table_name="ingest_retries")
    op.drop_index(op.f("ix_ingest_retries_request_id"), table_name="ingest_retries")
    op.drop_index(op.f("ix_ingest_retries_platform"), table_name="ingest_retries")
    op.drop_index(op.f("ix_ingest_retries_next_retry_at"), table_name="ingest_retries")
    op.drop_table("ingest_retries")

    op.drop_table("session_metrics")

    op.drop_index(op.f("ix_tasks_updated_at"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_session_id"), table_name="tasks")
    op.drop_index(op.f("ix_tasks_lane"), table_name="tasks")
    op.drop_table("tasks")

    op.drop_index(op.f("ix_messages_session_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_created_at"), table_name="messages")
    op.drop_table("messages")

    op.drop_index(op.f("ix_events_session_id"), table_name="events")
    op.drop_index(op.f("ix_events_platform"), table_name="events")
    op.drop_index(op.f("ix_events_created_at"), table_name="events")
    op.drop_table("events")

    op.drop_index(op.f("ix_sessions_platform"), table_name="sessions")
    op.drop_table("sessions")

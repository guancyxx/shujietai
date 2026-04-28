from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260428_0002"
down_revision = "20260428_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dead_letter_events",
        sa.Column("replay_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "dead_letter_events",
        sa.Column("replayed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "dead_letter_events",
        sa.Column("replayed_by", sa.String(length=128), nullable=True),
    )
    op.create_index(op.f("ix_dead_letter_events_replayed_at"), "dead_letter_events", ["replayed_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_dead_letter_events_replayed_at"), table_name="dead_letter_events")
    op.drop_column("dead_letter_events", "replayed_by")
    op.drop_column("dead_letter_events", "replayed_at")
    op.drop_column("dead_letter_events", "replay_count")

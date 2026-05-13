from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260513_0012"
down_revision = "20260511_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sessions", sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE sessions SET last_activity_at = started_at WHERE last_activity_at IS NULL")
    op.alter_column("sessions", "last_activity_at", nullable=False)


def downgrade() -> None:
    op.drop_column("sessions", "last_activity_at")
    op.drop_column("sessions", "last_read_at")

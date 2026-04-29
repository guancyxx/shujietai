from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260429_0004"
down_revision = "20260429_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_configs",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("system_configs")

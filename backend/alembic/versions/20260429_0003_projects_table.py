from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260429_0003"
down_revision = "20260428_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("repository_url", sa.String(length=1024), nullable=False),
        sa.Column("repository_name", sa.String(length=255), nullable=False),
        sa.Column("local_path", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_projects_code"), "projects", ["code"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_projects_code"), table_name="projects")
    op.drop_table("projects")

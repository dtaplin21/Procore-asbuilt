"""add procore_inspection_id to inspection_runs

Revision ID: b7c8d9e0f1a2
Revises: 94abb60704c6
Create Date: 2026-02-13

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "b7c8d9e0f1a2"
down_revision = "94abb60704c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inspection_runs",
        sa.Column("procore_inspection_id", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_inspection_runs_procore_inspection_id",
        "inspection_runs",
        ["procore_inspection_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_inspection_runs_procore_inspection_id",
        table_name="inspection_runs",
    )
    op.drop_column("inspection_runs", "procore_inspection_id")

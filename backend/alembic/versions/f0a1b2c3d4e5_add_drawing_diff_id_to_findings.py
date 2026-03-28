"""add drawing_diff_id to findings

Revision ID: f0a1b2c3d4e5
Revises: e8f9a0b1c2d3
Create Date: 2026-03-27

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f0a1b2c3d4e5"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "findings",
        sa.Column("drawing_diff_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_findings_drawing_diff_id",
        "findings",
        ["drawing_diff_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_findings_drawing_diff_id_drawing_diffs",
        "findings",
        "drawing_diffs",
        ["drawing_diff_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_findings_drawing_diff_id_drawing_diffs",
        "findings",
        type_="foreignkey",
    )
    op.drop_index("ix_findings_drawing_diff_id", table_name="findings")
    op.drop_column("findings", "drawing_diff_id")

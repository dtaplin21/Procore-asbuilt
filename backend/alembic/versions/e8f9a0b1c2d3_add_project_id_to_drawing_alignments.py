"""add project_id to drawing_alignments

Revision ID: e8f9a0b1c2d3
Revises: d8e9f0a1b2c3
Create Date: 2026-03-27

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "e8f9a0b1c2d3"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "drawing_alignments",
        sa.Column("project_id", sa.Integer(), nullable=True),
    )
    bind = op.get_bind()
    bind.execute(
        text(
            """
            UPDATE drawing_alignments
            SET project_id = (
                SELECT d.project_id
                FROM drawings d
                WHERE d.id = drawing_alignments.master_drawing_id
            )
            """
        )
    )
    op.alter_column(
        "drawing_alignments",
        "project_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.create_index(
        "ix_drawing_alignments_project_id",
        "drawing_alignments",
        ["project_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_drawing_alignments_project_id_projects",
        "drawing_alignments",
        "projects",
        ["project_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_drawing_alignments_project_id_projects",
        "drawing_alignments",
        type_="foreignkey",
    )
    op.drop_index("ix_drawing_alignments_project_id", table_name="drawing_alignments")
    op.drop_column("drawing_alignments", "project_id")

"""add inspection_run_id to drawing_inspection_reviews (alternate scope)

Revision ID: p4p1i5n8r0u1
Revises: p3p1a5c7e9g1
Create Date: 2026-06-23

Option A: reviews may scope to alignment_id (legacy) or inspection_run_id (inspection
overlay workflow). Exactly one scope column must be set. alignment_id becomes nullable
so new run-scoped rows do not require an alignment; drop alignment_id in a later PR.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p4p1i5n8r0u1"
down_revision = "p3p1a5c7e9g1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "drawing_inspection_reviews",
        sa.Column(
            "inspection_run_id",
            sa.Integer(),
            sa.ForeignKey("inspection_runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_drawing_inspection_reviews_inspection_run_id",
        "drawing_inspection_reviews",
        ["inspection_run_id"],
    )
    op.alter_column(
        "drawing_inspection_reviews",
        "alignment_id",
        existing_type=sa.Integer(),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_drawing_inspection_reviews_scope",
        "drawing_inspection_reviews",
        "(alignment_id is not null)::int + (inspection_run_id is not null)::int = 1",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_drawing_inspection_reviews_scope",
        "drawing_inspection_reviews",
        type_="check",
    )
    op.execute(
        sa.text(
            "DELETE FROM drawing_inspection_reviews WHERE alignment_id IS NULL"
        )
    )
    op.alter_column(
        "drawing_inspection_reviews",
        "alignment_id",
        existing_type=sa.Integer(),
        nullable=False,
    )
    op.drop_index(
        "ix_drawing_inspection_reviews_inspection_run_id",
        table_name="drawing_inspection_reviews",
    )
    op.drop_column("drawing_inspection_reviews", "inspection_run_id")

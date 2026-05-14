"""add drawing_inspection_reviews table

Revision ID: p3p1a5c7e9g1
Revises: p2p2r4t6v8w0
Create Date: 2026-05-05

Human / hybrid review of an alignment (optionally scoped to a drawing region).
Status supports simple tri-state and auto-vs-human pass labels.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p3p1a5c7e9g1"
down_revision = "p2p2r4t6v8w0"
branch_labels = None
depends_on = None

_REVIEW_STATUS = (
    "pending",
    "passed",
    "failed",
    "passed_auto",
    "passed_human",
)


def upgrade() -> None:
    op.create_table(
        "drawing_inspection_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "alignment_id",
            sa.Integer(),
            sa.ForeignKey("drawing_alignments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "region_id",
            sa.Integer(),
            sa.ForeignKey("drawing_regions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column(
            "reviewer_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("passed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            f"status IN ({', '.join(repr(s) for s in _REVIEW_STATUS)})",
            name="ck_drawing_inspection_reviews_status",
        ),
    )
    op.create_index(
        "ix_drawing_inspection_reviews_alignment_id",
        "drawing_inspection_reviews",
        ["alignment_id"],
    )
    op.create_index(
        "ix_drawing_inspection_reviews_region_id",
        "drawing_inspection_reviews",
        ["region_id"],
    )
    op.create_index(
        "ix_drawing_inspection_reviews_reviewer_user_id",
        "drawing_inspection_reviews",
        ["reviewer_user_id"],
    )
    op.create_index(
        "ix_drawing_inspection_reviews_status",
        "drawing_inspection_reviews",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_drawing_inspection_reviews_status", table_name="drawing_inspection_reviews")
    op.drop_index("ix_drawing_inspection_reviews_reviewer_user_id", table_name="drawing_inspection_reviews")
    op.drop_index("ix_drawing_inspection_reviews_region_id", table_name="drawing_inspection_reviews")
    op.drop_index("ix_drawing_inspection_reviews_alignment_id", table_name="drawing_inspection_reviews")
    op.drop_table("drawing_inspection_reviews")

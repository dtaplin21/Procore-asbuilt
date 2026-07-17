"""add drawing_match_candidates internal score table

Revision ID: p9d2m4c6a8n0
Revises: p8d1o3c5u7m9
Create Date: 2026-06-24

Stores backend-only match candidate scores for clue matching and vision confirmation.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p9d2m4c6a8n0"
down_revision = "p8d1o3c5u7m9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drawing_match_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("inspection_id", sa.String(), nullable=False),
        sa.Column(
            "inspection_run_id",
            sa.Integer(),
            sa.ForeignKey("inspection_runs.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "master_drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "region_id",
            sa.Integer(),
            sa.ForeignKey("drawing_regions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("bbox_json", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(), server_default="clue_match", nullable=False),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_drawing_match_candidates_inspection_id",
        "drawing_match_candidates",
        ["inspection_id"],
    )
    op.create_index(
        "ix_drawing_match_candidates_run_id",
        "drawing_match_candidates",
        ["inspection_run_id"],
    )
    op.create_index(
        "ix_drawing_match_candidates_master_drawing_id",
        "drawing_match_candidates",
        ["master_drawing_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_drawing_match_candidates_master_drawing_id",
        table_name="drawing_match_candidates",
    )
    op.drop_index(
        "ix_drawing_match_candidates_run_id",
        table_name="drawing_match_candidates",
    )
    op.drop_index(
        "ix_drawing_match_candidates_inspection_id",
        table_name="drawing_match_candidates",
    )
    op.drop_table("drawing_match_candidates")

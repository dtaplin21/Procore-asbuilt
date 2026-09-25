"""add drawing_legend_grounding_hits table

Revision ID: l1g2r3o4u5n6
Revises: s3y4m5b6o7l8
Create Date: 2026-09-25

Persist Document AI / template-match legend exemplar occurrences on master sheets.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "l1g2r3o4u5n6"
down_revision = "s3y4m5b6o7l8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "drawing_legend_grounding_hits" in inspector.get_table_names():
        return

    op.create_table(
        "drawing_legend_grounding_hits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "master_drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("grounding_run_id", sa.String(), nullable=False),
        sa.Column("legend_row_id", sa.Integer(), nullable=True),
        sa.Column("legend_label_text", sa.Text(), nullable=False),
        sa.Column("match_method", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False, server_default="document_ai"),
        sa.Column("bbox_json", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_drawing_legend_grounding_hits_master_drawing_id",
        "drawing_legend_grounding_hits",
        ["master_drawing_id"],
    )
    op.create_index(
        "ix_drawing_legend_grounding_hits_grounding_run_id",
        "drawing_legend_grounding_hits",
        ["grounding_run_id"],
    )
    op.create_index(
        "ix_drawing_legend_grounding_hits_drawing_page",
        "drawing_legend_grounding_hits",
        ["master_drawing_id", "page"],
    )


def downgrade() -> None:
    op.drop_index("ix_drawing_legend_grounding_hits_drawing_page", table_name="drawing_legend_grounding_hits")
    op.drop_index("ix_drawing_legend_grounding_hits_grounding_run_id", table_name="drawing_legend_grounding_hits")
    op.drop_index("ix_drawing_legend_grounding_hits_master_drawing_id", table_name="drawing_legend_grounding_hits")
    op.drop_table("drawing_legend_grounding_hits")

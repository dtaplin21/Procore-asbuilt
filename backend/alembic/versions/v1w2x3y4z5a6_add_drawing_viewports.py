"""add drawing_viewports table

Revision ID: v1w2x3y4z5a6
Revises: q2s3c4o5p6e7
Create Date: 2026-08-28

Per-viewport bbox + scale for multi-scale sheet digitization.
Feet conversion MUST use DrawingViewport.scale_json for geometry inside bbox;
drawings.scale_json remains a legacy titleblock hint only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "v1w2x3y4z5a6"
down_revision = "q2s3c4o5p6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "drawing_viewports" in inspector.get_table_names():
        return

    op.create_table(
        "drawing_viewports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("viewport_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("bbox_json", sa.JSON(), nullable=False),
        sa.Column("scale_json", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "drawing_id",
            "page",
            "viewport_id",
            name="uq_drawing_viewports_drawing_page_viewport",
        ),
    )
    op.create_index(
        "ix_drawing_viewports_drawing_id",
        "drawing_viewports",
        ["drawing_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "drawing_viewports" not in inspector.get_table_names():
        return

    op.drop_index(
        "ix_drawing_viewports_drawing_id",
        table_name="drawing_viewports",
    )
    op.drop_table("drawing_viewports")

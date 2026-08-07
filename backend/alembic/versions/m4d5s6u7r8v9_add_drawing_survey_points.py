"""add drawing_survey_points table

Revision ID: m4d5s6u7r8v9
Revises: m3d4i5n6d7x8
Create Date: 2026-08-06

Stores paired N/E survey coordinates indexed on drawings for coordinate matching.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "m4d5s6u7r8v9"
down_revision = "m3d4i5n6d7x8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "drawing_survey_points" in inspector.get_table_names():
        return

    op.create_table(
        "drawing_survey_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("northing", sa.Float(), nullable=False),
        sa.Column("easting", sa.Float(), nullable=False),
        sa.Column("station", sa.String(), nullable=True),
        sa.Column("structure_label", sa.String(), nullable=True),
        sa.Column("label_bbox_json", sa.JSON(), nullable=False),
        sa.Column("northing_bbox_json", sa.JSON(), nullable=True),
        sa.Column("easting_bbox_json", sa.JSON(), nullable=True),
        sa.Column("ocr_confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_drawing_survey_points_drawing_id",
        "drawing_survey_points",
        ["drawing_id"],
    )
    op.create_index(
        "ix_drawing_survey_points_drawing_page",
        "drawing_survey_points",
        ["drawing_id", "page"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "drawing_survey_points" not in inspector.get_table_names():
        return

    op.drop_index(
        "ix_drawing_survey_points_drawing_page",
        table_name="drawing_survey_points",
    )
    op.drop_index(
        "ix_drawing_survey_points_drawing_id",
        table_name="drawing_survey_points",
    )
    op.drop_table("drawing_survey_points")

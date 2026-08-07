"""add drawing_landmarks table

Revision ID: m5l6m7a8r9k0
Revises: m4d5s6u7r8v9
Create Date: 2026-08-06

Stores contour landmark fingerprints indexed on drawings for contour matching.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "m5l6m7a8r9k0"
down_revision = "m4d5s6u7r8v9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "drawing_landmarks" in inspector.get_table_names():
        return

    op.create_table(
        "drawing_landmarks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("landmark_type", sa.String(), nullable=False),
        sa.Column("bbox_json", sa.JSON(), nullable=False),
        sa.Column("hu_moments_json", sa.JSON(), nullable=False),
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
        "ix_drawing_landmarks_drawing_id",
        "drawing_landmarks",
        ["drawing_id"],
    )
    op.create_index(
        "ix_drawing_landmarks_drawing_page",
        "drawing_landmarks",
        ["drawing_id", "page"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "drawing_landmarks" not in inspector.get_table_names():
        return

    op.drop_index(
        "ix_drawing_landmarks_drawing_page",
        table_name="drawing_landmarks",
    )
    op.drop_index(
        "ix_drawing_landmarks_drawing_id",
        table_name="drawing_landmarks",
    )
    op.drop_table("drawing_landmarks")

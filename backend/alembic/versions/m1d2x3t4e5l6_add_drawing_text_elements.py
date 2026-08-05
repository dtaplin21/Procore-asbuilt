"""add drawing_text_elements OCR index table

Revision ID: m1d2x3t4e5l6
Revises: p0l1e2g3e4n5
Create Date: 2026-08-05

Stores positioned OCR / PDF text tokens on master drawings for clue-based matching.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "m1d2x3t4e5l6"
down_revision = "p0l1e2g3e4n5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "drawing_text_elements" in inspector.get_table_names():
        return

    op.create_table(
        "drawing_text_elements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "master_drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("text_normalized", sa.String(), nullable=False),
        sa.Column("bbox_json", sa.JSON(), nullable=False),
        sa.Column("ocr_confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("legend_expansion", sa.Text(), nullable=True),
        sa.Column("legend_codes_json", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_drawing_text_elements_master_drawing_id",
        "drawing_text_elements",
        ["master_drawing_id"],
    )
    op.create_index(
        "ix_drawing_text_elements_master_drawing_page",
        "drawing_text_elements",
        ["master_drawing_id", "page"],
    )
    op.create_index(
        "ix_drawing_text_elements_text_normalized",
        "drawing_text_elements",
        ["text_normalized"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "drawing_text_elements" not in inspector.get_table_names():
        return

    op.drop_index(
        "ix_drawing_text_elements_text_normalized",
        table_name="drawing_text_elements",
    )
    op.drop_index(
        "ix_drawing_text_elements_master_drawing_page",
        table_name="drawing_text_elements",
    )
    op.drop_index(
        "ix_drawing_text_elements_master_drawing_id",
        table_name="drawing_text_elements",
    )
    op.drop_table("drawing_text_elements")

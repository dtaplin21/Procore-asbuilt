"""add drawing_renditions table and drawing processing metadata

Revision ID: d8e9f0a1b2c3
Revises: 94c34a2d0c77
Create Date: 2026-02-13

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = "d8e9f0a1b2c3"
down_revision = "94c34a2d0c77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)

    # drawings: columns may already exist if schema was applied out-of-band
    drawing_col_names = {c["name"] for c in insp.get_columns("drawings")}
    if "original_filename" not in drawing_col_names:
        op.add_column(
            "drawings",
            sa.Column("original_filename", sa.String(), nullable=True),
        )
    if "processing_status" not in drawing_col_names:
        op.add_column(
            "drawings",
            sa.Column("processing_status", sa.String(), nullable=False, server_default="pending"),
        )
    if "processing_error" not in drawing_col_names:
        op.add_column(
            "drawings",
            sa.Column("processing_error", sa.Text(), nullable=True),
        )

    tables = insp.get_table_names()
    if "drawing_renditions" not in tables:
        op.create_table(
            "drawing_renditions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "drawing_id",
                sa.Integer(),
                sa.ForeignKey("drawings.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("page_number", sa.Integer(), nullable=False),
            sa.Column("image_storage_key", sa.String(), nullable=False),
            sa.Column("mime_type", sa.String(), nullable=False, server_default="image/png"),
            sa.Column("width_px", sa.Integer(), nullable=True),
            sa.Column("height_px", sa.Integer(), nullable=True),
            sa.Column("file_size", sa.Integer(), nullable=True),
            sa.Column("render_status", sa.String(), nullable=False, server_default="ready"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )

    # Re-inspect after possible create_table (new table / indexes)
    insp = inspect(bind)
    idx_names = {ix["name"] for ix in insp.get_indexes("drawing_renditions")}
    if "ix_drawing_renditions_drawing_id" not in idx_names:
        op.create_index(
            "ix_drawing_renditions_drawing_id",
            "drawing_renditions",
            ["drawing_id"],
        )
    uc_names = {uc["name"] for uc in insp.get_unique_constraints("drawing_renditions")}
    if "uq_drawing_renditions_drawing_page" not in uc_names:
        op.create_unique_constraint(
            "uq_drawing_renditions_drawing_page",
            "drawing_renditions",
            ["drawing_id", "page_number"],
        )


def downgrade() -> None:
    op.drop_constraint("uq_drawing_renditions_drawing_page", "drawing_renditions", type_="unique")
    op.drop_index("ix_drawing_renditions_drawing_id", table_name="drawing_renditions")
    op.drop_table("drawing_renditions")

    op.drop_column("drawings", "processing_error")
    op.drop_column("drawings", "processing_status")
    op.drop_column("drawings", "original_filename")

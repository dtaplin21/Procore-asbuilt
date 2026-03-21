"""add drawing_renditions table and drawing processing metadata

Revision ID: d8e9f0a1b2c3
Revises: 94c34a2d0c77
Create Date: 2026-02-13

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d8e9f0a1b2c3"
down_revision = "94c34a2d0c77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "drawings",
        sa.Column("original_filename", sa.String(), nullable=True),
    )
    op.add_column(
        "drawings",
        sa.Column("processing_status", sa.String(), nullable=False, server_default="pending"),
    )
    op.add_column(
        "drawings",
        sa.Column("processing_error", sa.Text(), nullable=True),
    )

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

    op.create_index(
        "ix_drawing_renditions_drawing_id",
        "drawing_renditions",
        ["drawing_id"],
    )
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

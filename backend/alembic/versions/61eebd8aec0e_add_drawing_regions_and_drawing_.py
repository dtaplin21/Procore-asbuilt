"""add drawing_regions and drawing_alignments

Revision ID: 61eebd8aec0e
Revises: c633122f53e5
Create Date: 2026-03-04 12:05:20.269349

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '61eebd8aec0e'
down_revision = 'c633122f53e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -----------------------------
    # drawing_regions
    # -----------------------------
    op.create_table(
        "drawing_regions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "master_drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("geometry", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_index(
        "ix_drawing_regions_master_drawing_id",
        "drawing_regions",
        ["master_drawing_id"],
    )

    # -----------------------------
    # drawing_alignments
    # -----------------------------
    op.create_table(
        "drawing_alignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "master_drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sub_drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "region_id",
            sa.Integer(),
            sa.ForeignKey("drawing_regions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("method", sa.String(length=50), nullable=False),
        sa.Column("transform", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_index(
        "ix_drawing_alignments_master_drawing_id",
        "drawing_alignments",
        ["master_drawing_id"],
    )

    op.create_index(
        "ix_drawing_alignments_sub_drawing_id",
        "drawing_alignments",
        ["sub_drawing_id"],
    )

    op.create_index(
        "ix_drawing_alignments_status",
        "drawing_alignments",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_drawing_alignments_status", table_name="drawing_alignments")
    op.drop_index("ix_drawing_alignments_sub_drawing_id", table_name="drawing_alignments")
    op.drop_index("ix_drawing_alignments_master_drawing_id", table_name="drawing_alignments")
    op.drop_table("drawing_alignments")

    op.drop_index("ix_drawing_regions_master_drawing_id", table_name="drawing_regions")
    op.drop_table("drawing_regions")


"""add drawing_markups

Revision ID: 6dd2129db6b0
Revises: i1n2d3e4x5o6
Create Date: 2026-10-25 20:11:06.287121

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "6dd2129db6b0"
down_revision = "i1n2d3e4x5o6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drawing_markups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("drawing_id", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("points_json", sa.JSON(), nullable=False),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("inspection_type", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("color", sa.String(length=9), nullable=True),
        sa.Column("created_by", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["drawing_id"], ["drawings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_drawing_markups_drawing_id"), "drawing_markups", ["drawing_id"], unique=False)
    op.create_index(
        op.f("ix_drawing_markups_inspection_type"), "drawing_markups", ["inspection_type"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_drawing_markups_inspection_type"), table_name="drawing_markups")
    op.drop_index(op.f("ix_drawing_markups_drawing_id"), table_name="drawing_markups")
    op.drop_table("drawing_markups")

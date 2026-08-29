"""add drawing_symbols table

Revision ID: s3y4m5b6o7l8
Revises: v1w2x3y4z5a6
Create Date: 2026-08-28

Persists detected/manual sheet symbols (class + fractional bbox + optional viewport).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "s3y4m5b6o7l8"
down_revision = "v1w2x3y4z5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "drawing_symbols" in inspector.get_table_names():
        return

    op.create_table(
        "drawing_symbols",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "drawing_id",
            sa.Integer(),
            sa.ForeignKey("drawings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("symbol_class", sa.String(), nullable=False),
        sa.Column("bbox_json", sa.JSON(), nullable=False),
        sa.Column("viewport_id", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("detector", sa.String(), nullable=False),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_drawing_symbols_drawing_id",
        "drawing_symbols",
        ["drawing_id"],
    )
    op.create_index(
        "ix_drawing_symbols_drawing_page",
        "drawing_symbols",
        ["drawing_id", "page"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "drawing_symbols" not in inspector.get_table_names():
        return

    op.drop_index("ix_drawing_symbols_drawing_page", table_name="drawing_symbols")
    op.drop_index("ix_drawing_symbols_drawing_id", table_name="drawing_symbols")
    op.drop_table("drawing_symbols")

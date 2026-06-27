"""add polygon_points to drawing_regions

Revision ID: c8f3b5d02e47
Revises: b7e2a4f91c36
Create Date: 2026-06-25

Optional normalized polygon detail for non-rectangular inspectable regions (Option A PR2/PR3).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c8f3b5d02e47"
down_revision = "b7e2a4f91c36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "drawing_regions",
        sa.Column("polygon_points", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("drawing_regions", "polygon_points")

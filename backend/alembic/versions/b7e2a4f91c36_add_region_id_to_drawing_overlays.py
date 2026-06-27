"""add region_id to drawing_overlays

Revision ID: b7e2a4f91c36
Revises: b4e8d2f1a3c5
Create Date: 2026-06-25

Links resolved overlays to drawing_regions for region-visibility (Option A PR1).
ON DELETE SET NULL preserves historical inspection rows when a region is removed.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7e2a4f91c36"
down_revision = "b4e8d2f1a3c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "drawing_overlays",
        sa.Column("region_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_drawing_overlays_region_id_drawing_regions",
        "drawing_overlays",
        "drawing_regions",
        ["region_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_drawing_overlays_region_id",
        "drawing_overlays",
        ["region_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_drawing_overlays_region_id", table_name="drawing_overlays")
    op.drop_constraint(
        "fk_drawing_overlays_region_id_drawing_regions",
        "drawing_overlays",
        type_="foreignkey",
    )
    op.drop_column("drawing_overlays", "region_id")

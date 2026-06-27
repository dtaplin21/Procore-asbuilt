"""add polygon geometry and audit timestamps to drawing_regions

Revision ID: c1d83f6a90e7
Revises: b7e2a4f91c36
Create Date: 2026-06-26

PR2 (region CRUD) needs created_at/updated_at on drawing_regions so
PATCH responses can report when a region was last edited. PR3 (region
editor) needs optional polygon geometry for non-rectangular regions —
added now, additive/nullable, so PR3 doesn't need its own migration
later.

``created_at`` and ``updated_at`` were already created on drawing_regions
in migration 61eebd8aec0e — this revision only adds ``polygon_points``.
The ORM uses timezone-aware DateTime defaults on those existing columns.

All new columns nullable/defaulted — existing rows need no manual backfill.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c1d83f6a90e7"
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

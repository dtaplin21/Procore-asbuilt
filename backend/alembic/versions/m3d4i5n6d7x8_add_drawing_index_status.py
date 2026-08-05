"""add drawing index job status columns

Revision ID: m3d4i5n6d7x8
Revises: m2d3s4c5a6l7
Create Date: 2026-08-05

Tracks master drawing auto-index job lifecycle separately from rendition processing_status.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "m3d4i5n6d7x8"
down_revision = "m2d3s4c5a6l7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("drawings")}

    if "index_status" not in columns:
        op.add_column(
            "drawings",
            sa.Column("index_status", sa.String(), nullable=False, server_default="pending"),
        )
        op.alter_column("drawings", "index_status", server_default=None)
    if "index_error" not in columns:
        op.add_column("drawings", sa.Column("index_error", sa.Text(), nullable=True))
    if "indexed_at" not in columns:
        op.add_column("drawings", sa.Column("indexed_at", sa.DateTime(), nullable=True))
    if "index_stats_json" not in columns:
        op.add_column("drawings", sa.Column("index_stats_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("drawings")}

    if "index_stats_json" in columns:
        op.drop_column("drawings", "index_stats_json")
    if "indexed_at" in columns:
        op.drop_column("drawings", "indexed_at")
    if "index_error" in columns:
        op.drop_column("drawings", "index_error")
    if "index_status" in columns:
        op.drop_column("drawings", "index_status")

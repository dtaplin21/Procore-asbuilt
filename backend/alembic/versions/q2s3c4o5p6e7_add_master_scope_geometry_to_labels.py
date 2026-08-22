"""add master_scope_geometry_json to location_match_labels

Revision ID: q2s3c4o5p6e7
Revises: q1m2c3a4n5j6
Create Date: 2026-06-24

Optional polyline/polygon ground truth for utility scope eval (PR-J J-1).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "q2s3c4o5p6e7"
down_revision = "q1m2c3a4n5j6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("location_match_labels")}
    if "master_scope_geometry_json" not in columns:
        op.add_column(
            "location_match_labels",
            sa.Column("master_scope_geometry_json", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("location_match_labels")}
    if "master_scope_geometry_json" in columns:
        op.drop_column("location_match_labels", "master_scope_geometry_json")

"""add scale_json and page_meta_json to drawings

Revision ID: m2d3s4c5a6l7
Revises: m1d2x3t4e5l6
Create Date: 2026-08-05

Stores parsed drawing scale and per-page dimension metadata for master auto-index.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "m2d3s4c5a6l7"
down_revision = "m1d2x3t4e5l6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("drawings")}

    if "scale_json" not in columns:
        op.add_column("drawings", sa.Column("scale_json", sa.JSON(), nullable=True))
    if "page_meta_json" not in columns:
        op.add_column("drawings", sa.Column("page_meta_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("drawings")}

    if "page_meta_json" in columns:
        op.drop_column("drawings", "page_meta_json")
    if "scale_json" in columns:
        op.drop_column("drawings", "scale_json")

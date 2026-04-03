"""add resolved to drawing_diffs

Revision ID: g7h8i9j0k1l2
Revises: f0a1b2c3d4e5
Create Date: 2026-04-01

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "g7h8i9j0k1l2"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("drawing_diffs")}
    if "resolved" not in cols:
        op.add_column(
            "drawing_diffs",
            sa.Column(
                "resolved",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
    insp = inspect(bind)
    idx_names = {ix["name"] for ix in insp.get_indexes("drawing_diffs")}
    if "ix_drawing_diffs_resolved" not in idx_names:
        op.create_index(
            "ix_drawing_diffs_resolved",
            "drawing_diffs",
            ["resolved"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = inspect(bind)
    idx_names = {ix["name"] for ix in insp.get_indexes("drawing_diffs")}
    if "ix_drawing_diffs_resolved" in idx_names:
        op.drop_index("ix_drawing_diffs_resolved", table_name="drawing_diffs")
    cols = {c["name"] for c in insp.get_columns("drawing_diffs")}
    if "resolved" in cols:
        op.drop_column("drawing_diffs", "resolved")

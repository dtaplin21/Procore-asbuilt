"""add progress_json to inspection_runs

Revision ID: r7u8n9p0r1o2
Revises: l1g2r3o4u5n6
Create Date: 2026-10-17

Coarse pipeline progress for inspection run UI polling.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "r7u8n9p0r1o2"
down_revision = "l1g2r3o4u5n6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inspection_runs",
        sa.Column("progress_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("inspection_runs", "progress_json")

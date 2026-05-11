"""add semantic_summary JSON to drawing_diffs

Revision ID: p2p2r4t6v8w0
Revises: p2p1m3n5o7q9
Create Date: 2026-05-05

Optional JSON for human-facing / LLM semantic narrative; structured detector output
remains in ``change_details``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p2p2r4t6v8w0"
down_revision = "p2p1m3n5o7q9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "drawing_diffs",
        sa.Column("semantic_summary", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("drawing_diffs", "semantic_summary")

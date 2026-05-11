"""add change_details JSON to drawing_diffs (semantic / structured metadata MVP)

Revision ID: p2p1m3n5o7q9
Revises: h2j4k6m8n0p1
Create Date: 2026-05-05

Optional JSON blob per diff for semantic summaries, detector provenance, future LLM output.
Geometry stays in ``diff_regions``; this column is non-geometric structured metadata only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p2p1m3n5o7q9"
down_revision = "h2j4k6m8n0p1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "drawing_diffs",
        sa.Column("change_details", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("drawing_diffs", "change_details")

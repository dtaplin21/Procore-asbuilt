"""add meta_json to drawing_match_candidates

Revision ID: q1m2c3a4n5j6
Revises: u0s1u2i3t4e5
Create Date: 2026-06-24

Stores agent fusion rationale and clue hits per internal match candidate.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "q1m2c3a4n5j6"
down_revision = "u0s1u2i3t4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("drawing_match_candidates")}
    if "meta_json" not in columns:
        op.add_column("drawing_match_candidates", sa.Column("meta_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("drawing_match_candidates")}
    if "meta_json" in columns:
        op.drop_column("drawing_match_candidates", "meta_json")

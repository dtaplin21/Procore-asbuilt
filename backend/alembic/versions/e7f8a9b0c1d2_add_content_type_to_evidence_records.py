"""add content_type to evidence_records

Revision ID: e7f8a9b0c1d2
Revises: 2d8d0a40aab6
Create Date: 2026-03-05

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "e7f8a9b0c1d2"
down_revision = "2d8d0a40aab6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evidence_records",
        sa.Column("content_type", sa.String(), nullable=True),
    )
    op.execute(
        """
        UPDATE evidence_records
        SET content_type = 'application/octet-stream'
        WHERE content_type IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("evidence_records", "content_type")

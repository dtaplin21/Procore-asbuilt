"""add status, source_id, dates, attachments_json, cross_refs_json to evidence_records

Revision ID: c4d5e6f7a8b9
Revises: a2b3c4d5e6f7
Create Date: 2026-02-13

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "c4d5e6f7a8b9"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evidence_records",
        sa.Column("status", sa.String(length=50), nullable=True, server_default="new"),
    )
    op.add_column(
        "evidence_records",
        sa.Column("source_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "evidence_records",
        sa.Column("dates", sa.JSON(), nullable=True),
    )
    op.add_column(
        "evidence_records",
        sa.Column("attachments_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "evidence_records",
        sa.Column("cross_refs_json", sa.JSON(), nullable=True),
    )
    op.alter_column(
        "evidence_records",
        "status",
        existing_type=sa.String(50),
        nullable=False,
        server_default="new",
    )


def downgrade() -> None:
    op.drop_column("evidence_records", "cross_refs_json")
    op.drop_column("evidence_records", "attachments_json")
    op.drop_column("evidence_records", "dates")
    op.drop_column("evidence_records", "source_id")
    op.drop_column("evidence_records", "status")

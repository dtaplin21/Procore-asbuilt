"""add review queue items for low-confidence or failed document extraction

Revision ID: p4r1q3u5e7i1
Revises: c1d83f6a90e7
Create Date: 2026-06-24

Backend-only queue for files that cannot be classified or extracted safely.
classification_confidence is never exposed to the frontend.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "p4r1q3u5e7i1"
down_revision = "c1d83f6a90e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_queue_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("file_id", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("document_type_guess", sa.String(), nullable=True),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("resolved", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_review_queue_items_file_id",
        "review_queue_items",
        ["file_id"],
    )
    op.create_index(
        "ix_review_queue_items_resolved",
        "review_queue_items",
        ["resolved"],
    )


def downgrade() -> None:
    op.drop_index("ix_review_queue_items_resolved", table_name="review_queue_items")
    op.drop_index("ix_review_queue_items_file_id", table_name="review_queue_items")
    op.drop_table("review_queue_items")
